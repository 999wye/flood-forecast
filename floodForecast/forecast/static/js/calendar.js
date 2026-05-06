// calendar.js — Custom calendar for history page

document.addEventListener('DOMContentLoaded', () => {
    const monthLabel = document.getElementById('calendarMonth');
    const daysGrid   = document.getElementById('calendarDays');
    const prevBtn    = document.getElementById('prevMonth');
    const nextBtn    = document.getElementById('nextMonth');

    const today       = new Date();
    let currentYear   = today.getFullYear();
    let currentMonth  = today.getMonth(); // 0-indexed

    const MONTH_NAMES = [
        'January','February','March','April','May','June',
        'July','August','September','October','November','December'
    ];

    function renderCalendar(year, month) {
        monthLabel.textContent = `${MONTH_NAMES[month]} ${year}`;
        daysGrid.innerHTML = '';

        const firstDay   = new Date(year, month, 1).getDay(); // 0=Sun
        const totalDays  = new Date(year, month + 1, 0).getDate();
        const datesData  = window.datesWithData || [];

        // Empty cells before first day
        for (let i = 0; i < firstDay; i++) {
            const empty = document.createElement('div');
            empty.classList.add('calendar__day', 'calendar__day--empty');
            daysGrid.appendChild(empty);
        }

        // Day cells
        for (let d = 1; d <= totalDays; d++) {
            const cell     = document.createElement('div');
            const dateStr  = `${year}-${String(month + 1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
            const isToday  = (d === today.getDate() && month === today.getMonth() && year === today.getFullYear());
            const hasData  = datesData.includes(dateStr);

            cell.classList.add('calendar__day');
            if (isToday)  cell.classList.add('calendar__day--today');
            if (hasData)  cell.classList.add('calendar__day--has-data');

            cell.textContent = d;

            if (hasData) {
                cell.addEventListener('click', () => {
                    // Remove active from all
                    document.querySelectorAll('.calendar__day--active')
                        .forEach(el => el.classList.remove('calendar__day--active'));
                    cell.classList.add('calendar__day--active');

                    // Call history fetch function
                    if (typeof window.onDateSelected === 'function') {
                        window.onDateSelected(dateStr);
                    }
                });
            }

            daysGrid.appendChild(cell);
        }
    }

    prevBtn.addEventListener('click', () => {
        currentMonth--;
        if (currentMonth < 0) { currentMonth = 11; currentYear--; }
        renderCalendar(currentYear, currentMonth);
    });

    nextBtn.addEventListener('click', () => {
        currentMonth++;
        if (currentMonth > 11) { currentMonth = 0; currentYear++; }
        renderCalendar(currentYear, currentMonth);
    });

    // Initial render
    renderCalendar(currentYear, currentMonth);
});
