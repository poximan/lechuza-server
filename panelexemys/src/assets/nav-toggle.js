(function () {
    function getWrapper() {
        return document.querySelector(".navbar-wrapper");
    }

    function closeMenu() {
        const wrapper = getWrapper();
        if (!wrapper) {
            return;
        }
        wrapper.classList.remove("mobile-nav-open");
        document.body.classList.remove("nav-locked");
    }

    function toggleMenu() {
        const wrapper = getWrapper();
        if (!wrapper) {
            return;
        }
        const isOpen = wrapper.classList.toggle("mobile-nav-open");
        document.body.classList.toggle("nav-locked", isOpen);
    }

    document.addEventListener("click", function (event) {
        const toggle = event.target.closest("#nav-toggle");
        if (toggle) {
            event.preventDefault();
            toggleMenu();
            return;
        }

        if (event.target.closest("#nav-overlay")) {
            closeMenu();
            return;
        }

        if (event.target.closest("#navbar-links-container .nav-link")) {
            closeMenu();
        }
    });
})();
