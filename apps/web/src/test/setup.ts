import '@testing-library/jest-dom/vitest'

// jsdom no implementa el desplazamiento de la ventana (la app lo usa al cambiar de pantalla).
window.scrollTo = () => undefined
