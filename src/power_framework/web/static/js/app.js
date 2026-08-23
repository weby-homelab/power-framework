/**
 * POWER Web UI Core Client Application Utilities
 */

function updateClock() {
    const now = new Date();
    const utcString = now.toISOString().substring(11, 19) + " UTC";
    const clockEl = document.getElementById("liveClock");
    const drawerClockEl = document.getElementById("drawerLiveClock");
    if (clockEl) {
        clockEl.textContent = utcString;
    }
    if (drawerClockEl) {
        drawerClockEl.textContent = utcString;
    }
}

document.addEventListener("DOMContentLoaded", () => {
    updateClock();
    setInterval(updateClock, 1000);

    const mobileMenuBtn = document.getElementById("mobileMenuBtn");
    const bottomMenuBtn = document.getElementById("bottomMenuBtn");
    const drawerCloseBtn = document.getElementById("drawerCloseBtn");
    const mobileDrawer = document.getElementById("mobileDrawer");
    const drawerBackdrop = document.getElementById("drawerBackdrop");
    let lastFocusedElement = null;

    if (!mobileDrawer || !drawerBackdrop) return;
    mobileDrawer.inert = true;

    const closeDrawer = () => {
        mobileDrawer.classList.remove("active");
        drawerBackdrop.classList.remove("active");
        mobileDrawer.setAttribute("aria-hidden", "true");
        drawerBackdrop.setAttribute("aria-hidden", "true");
        mobileDrawer.inert = true;
        if (mobileMenuBtn) mobileMenuBtn.setAttribute("aria-expanded", "false");
        document.body.style.overflow = "";
        if (lastFocusedElement instanceof HTMLElement)
            lastFocusedElement.focus();
    };

    const openDrawer = () => {
        lastFocusedElement = document.activeElement;
        mobileDrawer.inert = false;
        mobileDrawer.classList.add("active");
        drawerBackdrop.classList.add("active");
        mobileDrawer.setAttribute("aria-hidden", "false");
        drawerBackdrop.setAttribute("aria-hidden", "false");
        if (mobileMenuBtn) mobileMenuBtn.setAttribute("aria-expanded", "true");
        document.body.style.overflow = "hidden";
        if (drawerCloseBtn) drawerCloseBtn.focus();
    };

    if (mobileMenuBtn) mobileMenuBtn.addEventListener("click", openDrawer);
    if (bottomMenuBtn) bottomMenuBtn.addEventListener("click", openDrawer);
    if (drawerCloseBtn) drawerCloseBtn.addEventListener("click", closeDrawer);
    drawerBackdrop.addEventListener("click", closeDrawer);
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && mobileDrawer.classList.contains("active"))
            closeDrawer();
    });
});
