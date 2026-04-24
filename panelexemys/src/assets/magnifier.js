// Archivo: src/assets/magnifier.js

// Usamos la delegación de eventos para manejar elementos que pueden cargarse dinámicamente.
// Los eventos se adjuntan al 'document' y se filtran por su clase.

document.addEventListener('mouseover', function (e) {
    const container = e.target.closest('.magnifier-container');
    if (!container) {
        // No estamos sobre un contenedor, aseguramos que la lupa esté oculta.
        const loupe = document.querySelector('.magnifier-loupe');
        if (loupe) {
            loupe.style.display = 'none';
        }
        return;
    }

    const image = container.querySelector('.magnifier-image');
    const loupe = container.querySelector('.magnifier-loupe');

    if (!image || !loupe) {
        return; // Salir si no encontramos la imagen o la lupa
    }

    // Mostrar la lupa
    loupe.style.display = 'block';

    const zoomScale = 2;
    const loupeSize = 150;

    // Actualizar la posición de la lupa y el fondo cuando el mouse se mueve
    container.addEventListener('mousemove', function (e) {
        const rect = image.getBoundingClientRect();
        let x = e.clientX - rect.left;
        let y = e.clientY - rect.top;

        // Limitar las coordenadas
        x = Math.max(0, Math.min(x, rect.width));
        y = Math.max(0, Math.min(y, rect.height));

        // Posicionar la lupa en el centro del cursor
        loupe.style.left = `${x - loupeSize / 2}px`;
        loupe.style.top = `${y - loupeSize / 2}px`;

        // Posicionar y escalar la imagen de fondo de la lupa
        loupe.style.backgroundImage = `url(${image.src})`;
        loupe.style.backgroundSize = `${rect.width * zoomScale}px ${rect.height * zoomScale}px`;
        loupe.style.backgroundPosition = `-${x * zoomScale - loupeSize / 2}px -${y * zoomScale - loupeSize / 2}px`;
    });
});

document.addEventListener('mouseout', function (e) {
    // Si el mouse sale de cualquier parte del documento
    const container = e.target.closest('.magnifier-container');
    const loupe = document.querySelector('.magnifier-loupe');
    if (loupe && !container) {
        // Ocultar la lupa si no estamos dentro de un contenedor de lupa
        loupe.style.display = 'none';
    }
});