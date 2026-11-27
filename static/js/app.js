// Ask before deleting a cafe.
document.addEventListener("submit", event => {
    if (event.target.matches(".delete-form") && !confirm("Delete this cafe?")) {
        event.preventDefault();
    }
});