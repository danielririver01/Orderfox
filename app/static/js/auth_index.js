tailwind.config = {
    darkMode: 'media'
}

// Puente de sincronización tras OAuth. DEBE ser absoluto: en el flujo con
// Google el navegador sale del origen (Google → callback de Clerk) y una URL
// relativa puede perderse; Clerk entonces cae en su "Home URL" (config del
// dashboard) → landing sin sesión. Absoluta = siempre vuelve al sync.
var SYNC_BRIDGE_URL = window.location.origin + '/api/sync-clerk-redirect';

window.addEventListener('load', async function () {
    if (window.Clerk) {
        await window.Clerk.load({
            localization: {
                socialButtonsBlockButton__google: "Continuar con Google",
                signIn: {
                    start: {
                        title: 'Velzia',
                        subtitle: 'Tu asistente para gestionar el restaurante',
                        actionText: '¿Primera vez aquí?',
                        actionLink: 'Crea tu cuenta'
                    }
                },
                formFieldLabel__emailAddress: "Tu correo electrónico",
                formFieldInputPlaceholder__emailAddress: "tunombre@correo.com",
                formFieldLabel__password: "Tu contraseña",
                formFieldInputPlaceholder__password: "Tu contraseña",
                formButtonPrimary: "Entrar a mi negocio",
                // Errores en lenguaje humano: qué pasó + cómo solucionarlo.
                // Si Clerk no reconoce alguna clave, simplemente usa la suya.
                errors: {
                    form_identifier_not_found: {
                        title: 'No encontramos esa cuenta',
                        message: 'No hay ninguna cuenta con ese correo. Revisa cómo lo escribiste o crea una cuenta nueva.'
                    },
                    form_password_incorrect: {
                        title: 'Esa no es tu contraseña',
                        message: 'Inténtalo otra vez. Si no la recuerdas, usa "¿Olvidaste tu contraseña?".'
                    },
                    form_param_nil: {
                        title: 'Falta un dato',
                        message: 'Necesitamos tu correo y tu contraseña para entrar.'
                    },
                    form_password_length_too_short: {
                        title: 'Contraseña muy corta',
                        message: 'Escríbela completa: tiene más letras de las que pusiste.'
                    },
                    too_many_requests: {
                        title: 'Demasiados intentos',
                        message: 'Por seguridad, espera un minuto y vuelve a intentarlo.'
                    },
                    form_code_incorrect: {
                        title: 'El código no coincide',
                        message: 'Revisa el código que te llegó y escríbelo otra vez.'
                    }
                }
            }
        });

        // Esperar a que Clerk esté listo y la sesión restaurada
        await waitForClerkReady();

        // Si hay una sesión Clerk activa, sincronizar automáticamente SIN montar SignIn
        if (window.Clerk.user) {
            runSilentSync();
            return;
        }

        // Mount Clerk SignIn with dark orange theme
        const signInDiv = document.getElementById('clerk-signin');

        window.Clerk.mountSignIn(signInDiv, {
            afterSignInUrl: SYNC_BRIDGE_URL,
            afterSignUpUrl: SYNC_BRIDGE_URL,
            signIn: {
                socialButtons: {
                    providers: ['google']
                }
            },
            appearance: {
                baseTheme: window.Clerk.themes ? window.Clerk.themes.dark : undefined,
                variables: {
                    colorPrimary: '#f97316',
                    colorBackground: 'transparent',
                    colorText: '#f5f0eb',
                    colorTextSecondary: '#9a9088',
                    colorInputText: '#f5f0eb',
                    colorInputBackground: 'rgba(40, 34, 28, 0.9)',
                    colorNeutral: '#6b7280',
                    borderRadius: '0.75rem',
                },
                elements: {
                    rootBox: "w-full flex justify-center",
                    card: "w-full shadow-none border-none bg-transparent p-0",
                    headerTitle: "hidden",
                    headerSubtitle: "hidden",
                    socialButtonsBlockButton: "rounded-xl h-11 border-[rgba(249,115,22,0.2)] bg-[rgba(40,34,28,0.8)] hover:bg-[rgba(55,47,38,0.9)] hover:border-[rgba(249,115,22,0.4)] transition-all font-semibold text-[#f5f0eb]",
                    formButtonPrimary: "bg-[#f97316] hover:bg-[#fb923c] text-[#0a0a0a] text-sm font-bold h-12 rounded-xl shadow-[0_10px_28px_-10px_rgba(249,115,22,0.7)] transition-all",
                    footer: "hidden",
                    dividerRow: "my-5",
                    dividerText: "text-[10px] font-black text-gray-600 uppercase tracking-widest",
                    formFieldInput: 'bg-[rgba(40,34,28,0.9)] border-[rgba(249,115,22,0.2)] focus:ring-[#f97316]/20 focus:border-[#f97316] rounded-xl text-[#f5f0eb] placeholder-gray-600',
                    formFieldLabel: 'text-[#9a9088] font-medium',
                    otpCodeFieldInput: 'text-[#f5f0eb] bg-[rgba(40,34,28,0.9)] border-[rgba(249,115,22,0.25)] caret-[#f97316]',
                    identityPreviewEditButton: 'text-[#f97316]',
                    formResendCodeLink: 'text-[#f97316]',
                    alternativeMethodsBlockButton: 'text-[#f97316]',
                }
            }
        });

        // Listener para detectar si el usuario inicia sesión mientras está en la página
        window.Clerk.addListener(({ user }) => {
            if (user && !window.location.pathname.includes('/api/sync-clerk')) {
                runSilentSync();
            }
        });
    }
});

async function waitForClerkReady(maxWait = 5000) {
    const start = Date.now();
    while (Date.now() - start < maxWait) {
        if (window.Clerk?.isLoaded?.()) {
            // Pequeño delay extra para asegurar que la sesión se restauró
            await new Promise(r => setTimeout(r, 100));
            return;
        }
        await new Promise(r => setTimeout(r, 50));
    }
    console.warn('Clerk no estuvo listo a tiempo, continuando...');
}

async function runSilentSync() {
    const signInDiv = document.getElementById('clerk-signin');

    // Mostrar spinner de carga inmediatamente
    signInDiv.innerHTML = `
        <div class="flex flex-col items-center justify-center py-12">
            <div class="auth-spinner mb-4"></div>
            <p class="text-sm font-bold text-orange-400/90 animate-pulse">Estamos entrando a tu negocio…</p>
            <p class="text-xs text-gray-500 mt-1">Esto toma unos segundos.</p>
        </div>
    `;

    try {
        const token = await window.Clerk.session.getToken();
        const response = await fetch('/api/sync-clerk', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                clerk_id: window.Clerk.user.id,
                email: window.Clerk.user.primaryEmailAddress.emailAddress,
                session_id: window.Clerk.session.id
            })
        });

        const result = await response.json();
        if (result.success && result.redirect_url) {
            if (result.is_new_user) {
                const scannerSuffix = (window.VELZIA_CONFIG && window.VELZIA_CONFIG.scanner_available) ? ' y Escanear tus compras' : '';
                signInDiv.innerHTML = `
                    <div class="flex flex-col items-center justify-center py-12 px-6">
                        <div class="w-12 h-12 bg-green-500/10 rounded-full flex items-center justify-center mb-4 ring-1 ring-green-500/30">
                            <svg class="w-6 h-6 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                            </svg>
                        </div>
                        <p class="text-sm font-bold text-green-400 text-center mb-2">¡Bienvenido!</p>
                        <p class="text-xs text-gray-500 text-center mb-4">Tu plan de Prueba Premium (60 días) está activado con 50 créditos IA para Copilot VZ${scannerSuffix}</p>
                        <p class="text-xs text-gray-600 text-center">Redirigiendo...</p>
                    </div>
                `;
                setTimeout(() => {
                    window.location.href = result.redirect_url;
                }, 1500);
            } else {
                window.location.href = result.redirect_url;
            }
        } else if (result.error_code === 'USER_NOT_REGISTERED') {
            await window.Clerk.signOut();
            // Antes esta pantalla ofrecía "Intentar de nuevo": un botón que
            // NUNCA podía funcionar, porque la cuenta no existe. Se reemplaza
            // por el camino real (crear cuenta) + salida (usar otro correo).
            signInDiv.innerHTML = `
                <div class="flex flex-col items-center justify-center py-10 px-6 text-center">
                    <div class="w-14 h-14 bg-orange-500/10 rounded-full flex items-center justify-center mb-4 ring-1 ring-orange-500/30">
                        <svg class="w-7 h-7 text-orange-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path>
                        </svg>
                    </div>
                    <p class="text-base font-bold text-white mb-2">Todavía no tienes cuenta con ese correo</p>
                    <p class="text-sm text-gray-400 leading-relaxed mb-6">
                        Crea tu cuenta y prueba Velzia <strong class="text-white">60 días</strong>.
                        Toma menos de un minuto.
                    </p>
                    <a href="/planes"
                        class="w-full flex items-center justify-center bg-[#f97316] hover:bg-[#fb923c] text-[#0a0a0a] font-bold text-sm h-12 rounded-xl shadow-[0_10px_28px_-10px_rgba(249,115,22,0.7)] transition-all">
                        Ver planes y crear mi cuenta
                    </a>
                    <button onclick="window.location.reload()"
                        class="mt-3 text-sm font-semibold text-gray-500 hover:text-white underline decoration-dotted underline-offset-4 transition-colors">
                        Usar otro correo
                    </button>
                </div>
            `;
            return;
        } else {
            throw new Error("Sync failed");
        }
    } catch (error) {
        console.error("Silent sync failed, falling back to manual sign in", error);
        // Reintentar UNA vez. Si falla de nuevo, mostrar error en vez de
        // recargar en bucle infinito.
        if (!window.__velziaSyncRetried) {
            window.__velziaSyncRetried = true;
            window.location.reload();
            return;
        }
        signInDiv.innerHTML = `
            <div class="flex flex-col items-center justify-center py-12 px-6">
                <div class="w-12 h-12 bg-red-500/10 rounded-full flex items-center justify-center mb-4 ring-1 ring-red-500/30">
                    <svg class="w-6 h-6 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                </div>
                <p class="text-base font-bold text-white text-center mb-2">No pudimos conectarnos</p>
                <p class="text-sm text-gray-400 text-center leading-relaxed mb-5">
                    Revisa que tengas internet y vuelve a intentarlo.
                </p>
                <button onclick="window.location.reload()" class="px-6 h-11 bg-[#f97316] hover:bg-[#fb923c] text-[#0a0a0a] rounded-xl font-bold text-sm transition-colors shadow-[0_10px_28px_-10px_rgba(249,115,22,0.7)] active:scale-95">
                    Intentar de nuevo
                </button>
            </div>
        `;
    }
}
