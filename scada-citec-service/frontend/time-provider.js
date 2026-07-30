class TimeProvider {
    formatCurrentTimeForPresentation(locale = "es-AR") {
        return new Intl.DateTimeFormat(locale, {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: false,
            timeZone: "Etc/GMT+3",
        }).format(new Date());
    }
}

window.appTime = new TimeProvider();
