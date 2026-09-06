// static/javascript/ressources_editor.js

document.addEventListener('DOMContentLoaded', function () {
    initTwoWayDataBinding();
    initThemeSwatches();
    initZoomControls();
    initResetButtons();
});

/**
 * Synchronisation bidirectionnelle entre les inputs de la sidebar et les éléments de la feuille A4
 */
function initTwoWayDataBinding() {
    // 1. Sidebar Inputs -> Sheet Elements
    const boundInputs = document.querySelectorAll('[data-bind]');
    boundInputs.forEach(input => {
        const targetId = input.getAttribute('data-bind');
        const targetEl = document.getElementById(targetId);

        if (!targetEl) return;

        const updateTarget = () => {
            if (input.type === 'checkbox') {
                targetEl.style.display = input.checked ? '' : 'none';
            } else {
                targetEl.textContent = input.value;
            }
        };

        input.addEventListener('input', updateTarget);
        input.addEventListener('change', updateTarget);
    });

    // 2. Sheet Elements (contenteditable) -> Sidebar Inputs
    const editableElements = document.querySelectorAll('.editable[id]');
    editableElements.forEach(el => {
        el.setAttribute('contenteditable', 'true');
        el.addEventListener('input', function () {
            const boundInput = document.querySelector(`[data-bind="${el.id}"]`);
            if (boundInput) {
                boundInput.value = el.textContent;
            }
        });
    });
}

/**
 * Gestion des palettes de thèmes / couleurs
 */
function initThemeSwatches() {
    const swatches = document.querySelectorAll('.theme-swatch');
    const sheet = document.querySelector('.a4-sheet');

    if (!sheet) return;

    const themeColors = {
        gold: { primary: '#f59e0b', dark: '#b45309' },
        blue: { primary: '#3b82f6', dark: '#1d4ed8' },
        green: { primary: '#10b981', dark: '#047857' },
        purple: { primary: '#8b5cf6', dark: '#6d28d9' },
        coral: { primary: '#f43f5e', dark: '#be123c' },
        monochrome: { primary: '#334155', dark: '#0f172a' }
    };

    swatches.forEach(swatch => {
        swatch.addEventListener('click', function () {
            swatches.forEach(s => s.classList.remove('is-active'));
            this.classList.add('is-active');

            const theme = this.getAttribute('data-theme');
            if (themeColors[theme]) {
                sheet.style.setProperty('--res-primary', themeColors[theme].primary);
                sheet.style.setProperty('--res-primary-dark', themeColors[theme].dark);
            }
        });
    });
}

/**
 * Contrôles de zoom pour la prévisualisation A4
 */
function initZoomControls() {
    const sheet = document.querySelector('.a4-sheet');
    const container = document.querySelector('.studio-canvas-container');
    if (!sheet || !container) return;

    let currentZoom = 1.0;

    // Calcul automatique pour adapter la feuille à l'écran sur mobile / petits écrans
    function fitToScreen() {
        const containerWidth = container.clientWidth - 40; // padding
        const sheetWidth = sheet.offsetWidth || (sheet.classList.contains('landscape') ? 1122 : 793);
        if (containerWidth < sheetWidth) {
            currentZoom = Math.max(0.4, Number((containerWidth / sheetWidth).toFixed(2)));
        } else {
            currentZoom = 1.0;
        }
        applyZoom();
    }

    function applyZoom() {
        sheet.style.transform = `scale(${currentZoom})`;
        const zoomLabel = document.getElementById('zoomLevelLabel');
        if (zoomLabel) {
            zoomLabel.textContent = `${Math.round(currentZoom * 100)}%`;
        }
    }

    const btnZoomIn = document.getElementById('btnZoomIn');
    const btnZoomOut = document.getElementById('btnZoomOut');
    const btnZoomFit = document.getElementById('btnZoomFit');

    if (btnZoomIn) {
        btnZoomIn.addEventListener('click', () => {
            currentZoom = Math.min(1.5, Number((currentZoom + 0.1).toFixed(1)));
            applyZoom();
        });
    }

    if (btnZoomOut) {
        btnZoomOut.addEventListener('click', () => {
            currentZoom = Math.max(0.4, Number((currentZoom - 0.1).toFixed(1)));
            applyZoom();
        });
    }

    if (btnZoomFit) {
        btnZoomFit.addEventListener('click', fitToScreen);
    }

    // Ajustement initial automatique
    fitToScreen();
    window.addEventListener('resize', fitToScreen);

    // Réinitialisation du zoom pour l'impression 1:1 sans artefact
    window.addEventListener('beforeprint', () => {
        sheet.style.transform = 'none';
    });
    window.addEventListener('afterprint', () => {
        applyZoom();
    });
}

/**
 * Boutons de réinitialisation des formulaires
 */
function initResetButtons() {
    const resetBtn = document.getElementById('btnResetStudio');
    if (!resetBtn) return;

    resetBtn.addEventListener('click', function () {
        if (confirm('Voulez-vous réinitialiser tous les champs avec les valeurs par défaut ?')) {
            window.location.reload();
        }
    });
}
