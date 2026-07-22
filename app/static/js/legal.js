(function () {
    // ===== Menú móvil =====
    const menuToggle = document.getElementById('menuToggle');
    const menuOverlay = document.getElementById('menuOverlay');
    const mobileDrawer = document.getElementById('mobileDrawer');
    const drawerClose = document.getElementById('drawerClose');

    function openDrawer() {
        mobileDrawer.classList.add('open');
        menuOverlay.classList.add('open');
        document.body.style.overflow = 'hidden';
    }

    function closeDrawer() {
        mobileDrawer.classList.remove('open');
        menuOverlay.classList.remove('open');
        document.body.style.overflow = '';
    }

    if (menuToggle) menuToggle.addEventListener('click', openDrawer);
    if (drawerClose) drawerClose.addEventListener('click', closeDrawer);
    if (menuOverlay) menuOverlay.addEventListener('click', closeDrawer);

    // ===== Navegación activa =====
    const navLinks = document.querySelectorAll('.legal-nav-link');
    const sections = document.querySelectorAll('.legal-section');
    const activeIndicator = document.getElementById('activeIndicator');
    const activeSectionTitle = document.getElementById('activeSectionTitle');

    function setActiveSection(sectionId) {
        // Actualizar links
        navLinks.forEach(link => {
            link.classList.remove('active');
            if (link.getAttribute('data-section') === sectionId) {
                link.classList.add('active');
            }
        });

        // Actualizar indicador móvil
        const section = document.getElementById(sectionId);
        if (section && activeSectionTitle) {
            const name = section.getAttribute('data-section-name');
            activeSectionTitle.textContent = name;

            // Actualizar icono
            const iconSpan = activeIndicator.querySelector('.material-symbols-outlined');
            if (iconSpan) {
                const linkIcon = document.querySelector(`.legal-nav-link[data-section="${sectionId}"] .material-symbols-outlined`);
                if (linkIcon) iconSpan.textContent = linkIcon.textContent;
            }
        }
    }

    // Click en links de navegación
    navLinks.forEach(link => {
        link.addEventListener('click', function (e) {
            e.preventDefault();
            const sectionId = this.getAttribute('data-section');
            const target = document.getElementById(sectionId);

            if (target) {
                // Cerrar drawer en móvil
                if (window.innerWidth < 768) {
                    closeDrawer();
                }

                // Scroll a la sección
                setTimeout(() => {
                    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    setActiveSection(sectionId);
                }, window.innerWidth < 768 ? 300 : 0);
            }
        });
    });

    // ===== Detectar sección visible al hacer scroll (móvil) =====
    if (window.innerWidth < 768) {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const id = entry.target.getAttribute('id');
                    setActiveSection(id);
                }
            });
        }, { threshold: 0.3, rootMargin: '-80px 0px 0px 0px' });

        sections.forEach(section => observer.observe(section));
    }

    // ===== Escape para cerrar menú =====
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closeDrawer();
    });

    // ===== Botón Volver Arriba =====
    const backToTopBtn = document.getElementById('backToTop');
    const scrollThreshold = 200; // px antes de mostrar el botón

    function toggleBackToTop() {
        if (!backToTopBtn) return;
        if (window.scrollY > scrollThreshold) {
            backToTopBtn.classList.add('visible');
        } else {
            backToTopBtn.classList.remove('visible');
        }
    }

    if (backToTopBtn) {
        // Mostrar/ocultar al hacer scroll
        window.addEventListener('scroll', toggleBackToTop, { passive: true });

        // Scroll suave al inicio al hacer clic
        backToTopBtn.addEventListener('click', function () {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });

        // Verificar estado inicial
        toggleBackToTop();
    }
})();
