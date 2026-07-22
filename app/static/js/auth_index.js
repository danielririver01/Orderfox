tailwind.config = {
    darkMode: 'media'
}

window.addEventListener('load', async function () {
    if (window.Clerk) {
        await window.Clerk.load({
            localization: {
                socialButtonsBlockButton__google: "Continuar con Google",
                signIn: {
                    start: {
                        title: 'Velzia',
                        subtitle: 'Tu asistente para gestionar el restaurante',
                        actionText: '¿No tienes suscripción?',
                        actionLink: 'Ver planes'
                    }
                },
                formFieldLabel__emailAddress: "Correo electrónico",
                formFieldInputPlaceholder__emailAddress: "ejemplo@velzia.com",
                formFieldLabel__password: "Contraseña",
                formButtonPrimary: "INICIAR SESIÓN",
            }
        });

        // Silent Sync — if user already has a Clerk session, sync and redirect
        const hasFlashMessages = document.querySelector('.flash-message') !== null;
        if (window.Clerk.user && !hasFlashMessages) {
            const signInDiv = document.getElementById('clerk-signin');

            signInDiv.innerHTML = `
                <div class="flex flex-col items-center justify-center py-12">
                    <div class="auth-spinner mb-4"></div>
                    <p class="text-xs font-black text-orange-400/70 uppercase tracking-[0.2em] animate-pulse">Sincronizando sesión...</p>
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
                        const signInDiv = document.getElementById('clerk-signin');
                        signInDiv.innerHTML = `
                            <div class="flex flex-col items-center justify-center py-12 px-6">
                                <div class="w-12 h-12 bg-green-500/10 rounded-full flex items-center justify-center mb-4 ring-1 ring-green-500/30">
                                    <svg class="w-6 h-6 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                                    </svg>
                                </div>
                                <p class="text-sm font-bold text-green-400 text-center mb-2">¡Bienvenido!</p>
                                <p class="text-xs text-gray-500 text-center mb-4">Tu plan de Prueba Premium (90 días) está activado con 50 créditos IA para Copilot VZ y Escanear tus compras</p>
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
                    const message = result.message || 'Debe registrarse en la plataforma para poder acceder.';
                    const signInDiv = document.getElementById('clerk-signin');
                    signInDiv.innerHTML = `
                        <div class="flex flex-col items-center justify-center py-12 px-6">
                            <div class="w-12 h-12 bg-red-500/10 rounded-full flex items-center justify-center mb-4 ring-1 ring-red-500/30">
                                <svg class="w-6 h-6 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                                </svg>
                            </div>
                            <p class="text-sm font-bold text-red-400 text-center mb-4">${message}</p>
                            <button onclick="window.location.reload()" class="px-5 py-2 bg-orange-500 hover:bg-orange-600 text-white rounded-xl font-bold text-sm transition-colors shadow-lg shadow-orange-500/30">
                                Intentar de nuevo
                            </button>
                        </div>
                    `;
                    return;
                } else {
                    throw new Error("Sync failed");
                }
            } catch (error) {
                console.error("Silent sync failed, falling back to manual sign in", error);
                window.location.reload();
            }
            return;
        }

        // Mount Clerk SignIn with dark orange theme
        const signInDiv = document.getElementById('clerk-signin');

        window.Clerk.mountSignIn(signInDiv, {
            afterSignInUrl: '/',
            afterSignUpUrl: '/',
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
                    formButtonPrimary: "bg-[#f97316] hover:bg-[#ea6c0a] text-sm font-bold h-12 rounded-xl shadow-[0_10px_28px_-10px_rgba(249,115,22,0.7)] transition-all",
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
    }
});
