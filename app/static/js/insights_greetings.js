(function() {
    var greetings = [
        '¿En qué puedo ayudarte hoy?',
        '¿Qué necesitas saber?',
        '¿Cuál es tu consulta?',
        '¿En qué puedo asistirte?',
        'Cuéntame, ¿qué buscas?',
        '¿Qué vamos a resolver hoy?',
        'Dime, ¿qué necesitas?',
        '¿Qué información requieres?'
    ];
    var currentIdx = -1;

    function cycleGreeting() {
        var el = document.getElementById('vz-greeting');
        if (!el) return;
        currentIdx = (currentIdx + 1) % greetings.length;
        el.textContent = greetings[currentIdx];
    }

    var btn = document.getElementById('btn-new-conv');
    if (btn) btn.addEventListener('click', cycleGreeting);

    document.addEventListener('click', function(e) {
        var chip = e.target.closest('[data-quick]');
        if (chip) cycleGreeting();
    });

    currentIdx = Math.floor(Math.random() * greetings.length);
    var el = document.getElementById('vz-greeting');
    if (el) el.textContent = greetings[currentIdx];
})();
