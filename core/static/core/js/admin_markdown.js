window.addEventListener('load', function() {
    var editors = document.querySelectorAll('.markdown-editor');
    editors.forEach(function(textarea) {
        new EasyMDE({
            element: textarea,
            spellChecker: false,
            autosave: {
                enabled: false,
            },
            status: ["lines", "words"],
            toolbar: [
                "bold", "italic", "heading", "|", 
                "quote", "unordered-list", "ordered-list", "|", 
                "link", "table", "horizontal-rule", "|", 
                "preview", "side-by-side", "fullscreen"
            ]
        });
    });
});