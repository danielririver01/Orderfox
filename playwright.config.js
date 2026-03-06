// @ts-check
const { defineConfig, devices } = require('@playwright/test');

/**
 * Configuración de Playwright para Velzia (Flask App)
 * @see https://playwright.dev/docs/test-configuration
 */
module.exports = defineConfig({
  testDir: './tests',

  /* Ejecutar tests en paralelo */
  fullyParallel: false,

  /* Fallar en CI si dejaste test.only accidentalmente */
  forbidOnly: !!process.env.CI,

  /* Reintentar en CI */
  retries: process.env.CI ? 2 : 0,

  /* Workers paralelos */
  workers: process.env.CI ? 1 : 1,

  /* Reporter HTML interactivo */
  reporter: [['html', { open: 'never' }], ['list']],

  use: {
    /* URL base de tu app Flask */
    baseURL: 'http://localhost:5000',

    /* Capturar trace al reintentar un test fallido */
    trace: 'on-first-retry',

    /* Screenshot solo cuando falla */
    screenshot: 'only-on-failure',

    /* Video solo cuando falla */
    video: 'retain-on-failure',

    /* Timeout por acción */
    actionTimeout: 10000,
  },

  /* Solo Chromium para desarrollo local (más rápido) */
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    // Descomenta para agregar más navegadores:
    // { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    // { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],

  /* IMPORTANTE: Inicia tu servidor Flask antes de correr los tests:
   * En una terminal: flask run
   * En otra terminal: npx playwright test
   */
});

