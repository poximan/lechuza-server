(function () {
    const MINIMUM_SPLASH_MILLIS = 3_000;
    const splash = document.getElementById("lechuza-splash");
    const root = document.getElementById("react-entry-point");

    if (!splash || !root) {
        return;
    }

    let finished = false;
    let minimumDurationElapsed = false;
    const observer = new MutationObserver(checkReady);

    function pageIsReady() {
        const application = root.querySelector(".main-app-container");
        const pageContent = root.querySelector("#page-content");
        return Boolean(application && pageContent && pageContent.childElementCount > 0);
    }

    function removeSplash() {
        splash.remove();
    }

    function finish() {
        if (finished) {
            return;
        }
        finished = true;
        observer.disconnect();
        document.removeEventListener("dash:rendered", checkReady);
        document.body.classList.remove("lechuza-splash-active");
        splash.setAttribute("aria-hidden", "true");

        if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
            removeSplash();
            return;
        }

        splash.classList.add("is-leaving");
        splash.addEventListener("transitionend", function onTransitionEnd(event) {
            if (event.propertyName !== "opacity") {
                return;
            }
            splash.removeEventListener("transitionend", onTransitionEnd);
            removeSplash();
        });
    }

    function checkReady() {
        if (minimumDurationElapsed && pageIsReady()) {
            finish();
        }
    }

    observer.observe(root, { childList: true, subtree: true });
    document.addEventListener("dash:rendered", checkReady);
    window.setTimeout(function markMinimumDurationElapsed() {
        minimumDurationElapsed = true;
        checkReady();
    }, MINIMUM_SPLASH_MILLIS);
    checkReady();
})();
