tailwind.config = { darkMode: 'class' };

if (!window.__registerVerifyLoaded) {
    window.__registerVerifyLoaded = true;

    window.addEventListener('load', async function () {
        if (window.Clerk) {
            await window.Clerk.load({
                localization: {
                    socialButtonsBlockButton__google: "Continuar con Google",
                    socialButtonsBlockButton__facebook: "Continuar con Facebook",
                    signUp: {
                        start: {
                            title: "Únete a Velzia",
                            subtitle: "Crea tu cuenta y digitaliza tu restaurante"
                        }
                    },
                    formFieldLabel__firstName: "Nombre",
                    formFieldLabel__lastName: "Apellido",
                    formFieldInputPlaceholder__firstName: "Juan",
                    formFieldInputPlaceholder__lastName: "Pérez",
                    formFieldLabel__emailAddress: "Correo electrónico",
                    formFieldInputPlaceholder__emailAddress: "ejemplo@velzia.com",
                    formFieldLabel__password: "Contraseña",
                    formButtonPrimary: "CONTINUAR",
                    formFieldHintText__password: "Mínimo 8 caracteres, una mayúscula y un número.",
                    dividerText: "o también",
                    unstable__errors: {
                        password_too_short: "La contraseña es muy corta.",
                        password_missing_uppercase: "Falta una letra mayúscula.",
                        password_missing_number: "Falta un número."
                    }
                }
            });

            if (window.Clerk.user) {
                window.location.href = window.LOGIN_URL;
                return;
            }

            const signUpDiv = document.getElementById('clerk-signup');

            window.Clerk.mountSignUp(signUpDiv, {
                afterSignUpUrl: '/',
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
                    }
                }
            });
        }
    });
}
