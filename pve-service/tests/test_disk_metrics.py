import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

os.environ.update({
    'PVE_BASE_URL': 'https://unused/api2/json', 'PVE_API_TOKEN': 'test!token=secret',
    'PVE_NODE_NAME': 'node', 'PVE_VHOST_IDS': '100,101', 'PVE_HTTP_TIMEOUT_SECONDS': '5',
    'PVE_VERIFY_SSL': 'true', 'PVE_POLL_INTERVAL_SECONDS': '120', 'PVE_HISTORY_HOURS': '72',
    'PVE_MQTT_PUBLISH_FACTOR': '5', 'PVE_DATA_DIR': '/unused', 'PVE_STATE_FILE': 'state.json',
    'PVE_HISTORY_FILE': 'history.json', 'ALARM_INTERNAL_API_KEY': 'test-key',
    'MQTT_TOPIC_PROXMOX_ESTADO': 'test/pve', 'MQTT_PUBLISH_QOS_STATE': '1',
    'MQTT_PUBLISH_RETAIN_STATE': 'false',
})
from src import collector, history
from src.disk_metrics import agent_enabled, configured_disks, guest_filesystems, host_storages, usage


def filesystem(name='sda1', mount='/', used=0, total=100):
    return {'name': name, 'mountpoint': mount, 'type': 'ext4', 'used-bytes': used,
            'total-bytes': total, 'disk': [{'bus-type': 'scsi', 'bus': 0, 'target': 0, 'unit': 0}]}


class DiskMetricsTests(unittest.TestCase):
    def setUp(self):
        self.collector = collector.PveCollector()
        self.collector._session = Mock()
        self.collector._get = Mock()

    def test_all_data_disks_are_listed_with_exact_configured_size(self):
        disks = configured_disks({'scsi10': 'local:disk10,size=1.5T', 'scsi2': 'local:disk2,size=0.5G',
                                  'virtio0': 'file=local:disk0,size=20G', 'sata0': 'local:sata,size=128M',
                                  'ide2': 'local:installer.iso,media=cdrom,size=900M',
                                  'efidisk0': 'local:efi,size=4M', 'unused0': 'local:detached',
                                  'scsihw': 'virtio-scsi-single', 'ide0': 'none,media=cdrom'})
        self.assertEqual([disk['id'] for disk in disks], ['sata0', 'scsi2', 'scsi10', 'virtio0'])
        self.assertEqual(disks[1]['total_bytes'], 512 * 1024**2)
        self.assertEqual(disks[2]['total_bytes'], 1536 * 1024**3)
        self.assertEqual(disks[3]['volume'], 'local:disk0')
        self.assertIsNone(configured_disks({'scsi0': 'local:disk,size=bad'})[0]['total_bytes'])

    def test_guest_agent_configuration_parses_enabled_flag(self):
        for raw in ('1', 'enabled=1,fstrim_cloned_disks=1', '1,type=virtio'):
            self.assertTrue(agent_enabled({'agent': raw}))
        for config in ({}, {'agent': '0'}, {'agent': 'enabled=0,type=virtio'}):
            self.assertFalse(agent_enabled(config))

    def test_zero_is_measured_and_missing_is_unknown(self):
        rows = guest_filesystems({'result': [filesystem(), {'name': 'sdb', 'mountpoint': '/data', 'type': 'xfs', 'disk': []}]})
        self.assertEqual(rows[0]['used_bytes'], 0)
        self.assertEqual(rows[0]['used_pct'], 0)
        self.assertIsNone(rows[1]['used_bytes'])
        self.assertIsNone(rows[1]['used_pct'])
        for invalid in (True, -1, float('nan'), '0'):
            self.assertIsNone(usage(invalid, 100)['used_pct'])

    def test_volumes_are_not_assigned_to_disks_by_position_or_added_together(self):
        lvm = filesystem('dm-0', '/data', 70, 100)
        lvm['disk'].append({'bus-type': 'scsi', 'bus': 0, 'target': 1, 'unit': 0})
        rows = guest_filesystems({'result': [lvm, filesystem('sda1', '/boot', 10, 20), lvm]})
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(rows[1]['devices']), 2)
        self.assertEqual(rows[1]['used_pct'], 70)
        self.assertNotIn('disk_id', rows[1])

    def test_privileged_capacity_and_reserved_available_space(self):
        row = filesystem(used=20, total=90)
        row['total-bytes-privileged'] = 100
        self.assertEqual(guest_filesystems({'result': [row]})[0]['used_pct'], 20)
        self.assertEqual(usage(20, 100, 70)['available_bytes'], 70)

    def test_invalid_agent_response_is_not_an_empty_measurement(self):
        for data in (None, [], {'result': {}}, {'result': [None]}):
            with self.assertRaises(ValueError):
                guest_filesystems(data)

    def test_storage_rows_preserve_shared_and_inactive_and_do_not_sum(self):
        rows = host_storages([{'storage': 'local', 'type': 'dir', 'enabled': 1, 'active': 1,
                              'used': 20, 'total': 100, 'avail': 70},
                             {'storage': 'backup', 'type': 'pbs', 'shared': 1, 'enabled': 1, 'active': 0},
                             {'storage': 'disabled', 'enabled': 0}])
        self.assertEqual([row['id'] for row in rows], ['backup', 'local'])
        self.assertTrue(rows[0]['shared'])
        self.assertFalse(rows[0]['active'])
        self.assertIsNone(rows[0]['used_bytes'])
        self.assertEqual(rows[1]['used_pct'], 20)

    def test_agent_is_not_queried_when_disabled_or_vm_stopped(self):
        for config, running, status in (({}, True, 'agent_disabled'), ({'agent': '1'}, False, 'stopped')):
            self.collector._get.reset_mock()
            self.collector._get.return_value = {'scsi0': 'local:disk,size=20G', **config}
            result = self.collector._guest_disks(100, running)
            self.assertEqual(result['disk_usage_status'], status)
            self.assertEqual(result['filesystems'], [])
            self.assertEqual(len(result['virtual_disks']), 1)
            self.collector._get.assert_called_once_with('/nodes/node/qemu/100/config')

    def test_forbidden_agent_is_explicit_without_inventing_zero_usage(self):
        response = requests.Response()
        response.status_code = 403
        self.collector._get.side_effect = [{'agent': '1', 'scsi0': 'local:disk,size=20G'},
                                           requests.HTTPError(response=response)]
        result = self.collector._guest_disks(100, True)
        self.assertEqual(result['disk_usage_status'], 'permission_denied')
        self.assertIn('VM.Monitor', result['disk_usage_error'])
        self.assertEqual(result['filesystems'], [])
        self.assertEqual(len(result['virtual_disks']), 1)

    def test_agent_success_and_missing_values_have_different_status(self):
        for row, expected in ((filesystem(used=25), 'ok'),
                              ({'name': 'sda', 'mountpoint': '/', 'type': 'ext4'}, 'partial')):
            self.collector._get.side_effect = [{'agent': '1'}, {'result': [row]}]
            result = self.collector._guest_disks(100, True)
            self.assertEqual(result['disk_usage_status'], expected)
            self.assertEqual(len(result['filesystems']), 1)

    def test_agent_failure_keeps_vm_metrics_and_host_storage_is_only_at_top_level(self):
        self.collector._fetch_qemu = Mock(return_value=[{'vmid': 100, 'status': 'running', 'name': 'vm100'}])
        self.collector._fetch_status = Mock(return_value={'cpu': .25, 'mem': 25, 'maxmem': 100,
                                                        'maxdisk': 20 * 1024**3, 'disk': 0})
        self.collector._get.side_effect = [
            {'agent': '1', 'scsi0': 'local:disk,size=20G'}, requests.Timeout(),
            {'rootfs': {'used': 20, 'total': 100, 'avail': 70}},
            [{'storage': 'local', 'type': 'dir', 'enabled': 1, 'active': 1, 'used': 20, 'total': 100}],
        ]
        result, _ = self.collector.collect()
        self.assertEqual(result['status'], 'online')
        self.assertEqual(result['missing'], [101])
        vm = result['vms'][0]
        self.assertEqual(vm['cpu_pct'], 25)
        self.assertEqual(vm['mem_pct'], 25)
        self.assertIsNone(vm['disk_pct'])
        self.assertEqual(vm['disk_usage_status'], 'agent_unavailable')
        self.assertNotIn('host_storage', vm)
        self.assertEqual(result['host_storage']['rootfs']['used_pct'], 20)

    def test_host_storage_failure_does_not_hide_other_storage_data(self):
        self.collector._get.side_effect = [requests.Timeout(), [
            {'storage': 'local', 'enabled': 1, 'active': 1, 'used': 0, 'total': 100}]]
        result = self.collector._host_storage()
        self.assertIsNone(result['rootfs'])
        self.assertEqual(len(result['errors']), 1)
        self.assertEqual(result['storages'][0]['used_pct'], 0)

    def test_cpu_and_memory_history_continue_when_disk_usage_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(history.cfg, 'DATA_DIR', directory), \
                patch.object(history, '_HISTORY_CACHE', None):
            history.update_history({'ts': '2026-10-28T11:00:00Z', 'vms': [
                {'vmid': 100, 'name': 'vm100', 'cpu_pct': 25, 'mem_pct': 30, 'disk_pct': None}]}, 120, 72)
            result, _ = history.load_history_for_dashboard()
            self.assertEqual(result[100]['history']['cpu_pct'][0]['value'], 25)
            self.assertEqual(result[100]['history']['mem_pct'][0]['value'], 30)
            self.assertEqual(result[100]['history']['disk_pct'], [])
            self.assertTrue((Path(directory) / 'history.json').is_file())


if __name__ == '__main__':
    unittest.main()
