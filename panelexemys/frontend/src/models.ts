export type JsonValue = string | number | boolean | null | JsonRecord | JsonValue[];
export type JsonRecord = { [key: string]: JsonValue };

export interface NavigationItem {
  label: string;
  href: string;
  protected: boolean;
}

export interface NavigationContract {
  base_path: string;
  mode: "secure" | "protected";
  refresh_ms: number;
  items: NavigationItem[];
}
