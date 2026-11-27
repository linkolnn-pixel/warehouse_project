const documentDate = document.getElementById("id_date");

if (documentDate && typeof window.flatpickr === "function" && window.flatpickr.l10ns.ru) {
    window.flatpickr(documentDate, {
        enableTime: true,
        time_24hr: true,
        minuteIncrement: 1,
        locale: "ru",
        dateFormat: "Y-m-d\\TH:i",
        altInput: true,
        altFormat: "d.m.Y H:i",
        allowInput: true,
        disableMobile: true,
        monthSelectorType: "static",
        onReady(_dates, _value, calendar) {
            calendar.altInput.id = `${documentDate.id}-display`;
            calendar.altInput.placeholder = "ДД.ММ.ГГГГ ЧЧ:ММ";
            document.querySelector(`label[for="${documentDate.id}"]`).htmlFor = calendar.altInput.id;
        },
    });
}
