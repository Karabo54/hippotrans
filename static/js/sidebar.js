// Wait until the page is fully loaded
document.addEventListener("DOMContentLoaded", function () {

    // Get all expandable menu items
    const menus = document.querySelectorAll(".has-sub");

    // Restore previously opened menu (if any)
    const activeMenu = localStorage.getItem("activeMenu");

    if (activeMenu) {
        const menuToOpen = document.querySelector(
            `.has-sub[data-menu="${activeMenu}"]`
        );

        // Add 'open' class to keep it expanded
        if (menuToOpen) {
            menuToOpen.classList.add("open");
        }
    }

    // Loop through each menu
    menus.forEach(menu => {

        const link = menu.querySelector(".menu-link");

        link.addEventListener("click", function (e) {
            e.preventDefault(); // Stop page jump

            const menuName = menu.getAttribute("data-menu");

            // If menu already open → close it
            if (menu.classList.contains("open")) {
                menu.classList.remove("open");
                localStorage.removeItem("activeMenu");
            } else {
                // Close other menus
                menus.forEach(m => m.classList.remove("open"));

                // Open clicked menu
                menu.classList.add("open");

                // Save open menu in browser memory
                localStorage.setItem("activeMenu", menuName);
            }
        });
    });
});
