// static/javascript/ressources_editor.js

document.addEventListener('DOMContentLoaded', function () {
    initTwoWayDataBinding();
    initThemeSwatches();
    initZoomControls();
    initResetButtons();
});

/**
 * Rendre un élément pleinement éditable avec gestion des événements
 */
function makeElementEditable(el) {
    if (!el.hasAttribute('contenteditable')) {
        el.setAttribute('contenteditable', 'true');
        el.setAttribute('spellcheck', 'false');
    }

    // Gestion du clic pour garantir la prise de focus immédiate
    el.addEventListener('click', function (e) {
        if (document.activeElement !== el) {
            el.focus();
        }
    });

    // Empêcher les sauts de ligne intempestifs sur les titres et étiquettes monolignes
    el.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !el.dataset.multiline && !el.classList.contains('diplome-reason')) {
            e.preventDefault();
            el.blur();
        }
    });

    // Collage en texte brut uniquement (pas de styles HTML parasites)
    el.addEventListener('paste', function (e) {
        e.preventDefault();
        const text = (e.clipboardData || window.clipboardData).getData('text/plain');
        if (document.queryCommandSupported && document.queryCommandSupported('insertText')) {
            document.execCommand('insertText', false, text);
        } else {
            const selection = window.getSelection();
            if (selection.rangeCount) {
                const range = selection.getRangeAt(0);
                range.deleteContents();
                range.insertNode(document.createTextNode(text));
                range.collapse(false);
            }
        }
    });
}

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

            // Si c'est le champ destinataire du diplôme, vérifier la cohérence avec le selecteur d'élèves
            if (targetId === 'diplomeRecipient') {
                const studentSelector = document.getElementById('studentSelector');
                if (studentSelector) {
                    let matched = false;
                    for (let opt of studentSelector.options) {
                        const optName = opt.getAttribute('data-name');
                        if (optName && optName.trim().toLowerCase() === input.value.trim().toLowerCase()) {
                            studentSelector.value = opt.value;
                            matched = true;
                            break;
                        }
                    }
                    if (!matched) {
                        studentSelector.value = '';
                    }
                }
            }
        };

        input.addEventListener('input', updateTarget);
        input.addEventListener('change', updateTarget);
    });

    // 2. Initialiser tous les éléments .editable actuels
    const editableElements = document.querySelectorAll('.editable');
    editableElements.forEach(el => makeElementEditable(el));

    // 3. Écoute globale de la saisie sur la feuille (délégation d'événements)
    const printableSheet = document.getElementById('printableSheet');
    if (printableSheet) {
        printableSheet.addEventListener('input', function (e) {
            const el = e.target.closest('.editable');
            if (!el) return;

            // Si l'élément est relié à un input de la barre latérale
            if (el.id) {
                const boundInput = document.querySelector(`[data-bind="${el.id}"]`);
                if (boundInput) {
                    const text = el.innerText !== undefined ? el.innerText.trim() : el.textContent.trim();
                    boundInput.value = text;

                    // Si c'est le nom de l'élève sur le diplôme
                    if (el.id === 'diplomeRecipient') {
                        const studentSelector = document.getElementById('studentSelector');
                        if (studentSelector) {
                            let matched = false;
                            for (let opt of studentSelector.options) {
                                const optName = opt.getAttribute('data-name');
                                if (optName && optName.trim().toLowerCase() === text.toLowerCase()) {
                                    studentSelector.value = opt.value;
                                    matched = true;
                                    break;
                                }
                            }
                            if (!matched) {
                                studentSelector.value = '';
                            }
                        }
                    }
                }
            }
        });

        // 4. Observer les ajouts dynamiques dans la feuille (ex: génération dynamique de codes-barres)
        const observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                mutation.addedNodes.forEach(function (node) {
                    if (node.nodeType === 1) {
                        if (node.classList.contains('editable')) {
                            makeElementEditable(node);
                        }
                        node.querySelectorAll && node.querySelectorAll('.editable').forEach(el => makeElementEditable(el));
                    }
                });
            });
        });
        observer.observe(printableSheet, { childList: true, subtree: true });
    }
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
    const supportsZoom = 'zoom' in document.body.style;

    // Calcul automatique pour adapter la feuille à l'écran sur mobile / petits écrans
    function fitToScreen() {
        const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
        const isMobile = viewportWidth <= 1023;
        const padding = isMobile ? 24 : 40;
        // Sur mobile, l'espace disponible réel est borné par le viewport pour éviter
        // qu'une feuille non zoomée n'élargisse artificiellement container.clientWidth
        const availableWidth = isMobile
            ? Math.max(100, viewportWidth - padding)
            : Math.max(100, container.clientWidth - padding);

        const sheetWidth = sheet.classList.contains('landscape') ? 1122 : 794;
        if (availableWidth < sheetWidth) {
            currentZoom = Math.max(0.2, Number((availableWidth / sheetWidth).toFixed(2)));
        } else {
            currentZoom = 1.0;
        }
        applyZoom();
    }

    function applyZoom() {
        if (supportsZoom) {
            sheet.style.zoom = currentZoom;
            sheet.style.transform = 'none';
        } else {
            sheet.style.transform = `scale(${currentZoom})`;
            sheet.style.transformOrigin = 'top center';
            const sheetWidth = sheet.classList.contains('landscape') ? 1122 : 794;
            const scaledWidth = sheetWidth * currentZoom;
            const marginComp = (scaledWidth - sheetWidth) / 2;
            sheet.style.marginLeft = `${marginComp}px`;
            sheet.style.marginRight = `${marginComp}px`;
        }
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
            currentZoom = Math.min(1.5, Number((currentZoom + 0.1).toFixed(2)));
            applyZoom();
        });
    }

    if (btnZoomOut) {
        btnZoomOut.addEventListener('click', () => {
            currentZoom = Math.max(0.2, Number((currentZoom - 0.1).toFixed(2)));
            applyZoom();
        });
    }

    if (btnZoomFit) {
        btnZoomFit.addEventListener('click', fitToScreen);
    }

    // Ajustement initial automatique et réactivité
    fitToScreen();
    window.addEventListener('resize', fitToScreen);
    window.addEventListener('orientationchange', () => setTimeout(fitToScreen, 150));
    window.addEventListener('load', fitToScreen);

    // Réinitialisation du zoom pour l'impression 1:1 sans artefact
    window.addEventListener('beforeprint', () => {
        if (supportsZoom) {
            sheet.style.zoom = '1';
        }
        sheet.style.transform = 'none';
        sheet.style.marginLeft = '';
        sheet.style.marginRight = '';
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
