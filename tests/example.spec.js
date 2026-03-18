// @ts-check
const { test, expect } = require('@playwright/test');

// =====================================================
// TESTS DE VELZIA - Autenticación
// Rutas obtenidas de los blueprints Flask:
//   auth_bp  → sin url_prefix (rutas desde la raíz)
//   dashboard_bp → url_prefix='/dashboard'
// IMPORTANTE: Tener Flask corriendo: flask run
// =====================================================

test.describe('Página de Login', () => {
  test('muestra el formulario de login correctamente', async ({ page }) => {
    // Login está en la raíz: auth_bp.route('/')
    await page.goto('/');

    // Verificar que cargó la página
    await expect(page).toHaveTitle(/Velzia|Login|Iniciar/i);

    // Verificar que existen los campos del formulario
    await expect(page.locator('input[type="email"], input[name="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"], input[name="password"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });

  test('muestra error con credenciales inválidas', async ({ page }) => {
    await page.goto('/');

    await page.fill('input[type="email"], input[name="email"]', 'invalido@test.com');
    await page.fill('input[type="password"], input[name="password"]', 'wrongpassword123');
    await page.click('button[type="submit"]');

    // Esperar respuesta del servidor
    await page.waitForTimeout(1500);

    // Debe permanecer en la raíz (login) o mostrar un mensaje de error
    const currentUrl = page.url();
    expect(currentUrl).toMatch(/localhost:5000\/?$/);
  });
});

test.describe('Página Forgot Password', () => {
  test('muestra el formulario de recuperación de contraseña', async ({ page }) => {
    // auth_bp.route('/forgot-password')
    await page.goto('/forgot-password');

    // Verificar que existe el campo de email
    await expect(page.locator('input[type="email"], input[name="email"]')).toBeVisible();
  });
});

test.describe('Redirecciones de autenticación', () => {
  test('redirige al login si accede a /dashboard sin autenticación', async ({ page }) => {
    // dashboard_bp tiene url_prefix='/dashboard', ruta '/' → /dashboard/
    await page.goto('/dashboard/');

    // El decorador @login_required redirige a la raíz (login)
    await expect(page).toHaveURL(/localhost:5000\/?$/);
  });
});
