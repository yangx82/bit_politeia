/**
 * Formats a date or ISO string to yyyy-mm-dd HH:MM
 */
export const formatTime = (isoString) => {
    if (!isoString) return ''
    try {
        const date = new Date(isoString);
        if (isNaN(date.getTime())) return String(isoString);
        
        const y = date.getFullYear();
        const m = String(date.getMonth() + 1).padStart(2, '0');
        const d = String(date.getDate()).padStart(2, '0');
        const hh = String(date.getHours()).padStart(2, '0');
        const mm = String(date.getMinutes()).padStart(2, '0');
        return `${y}-${m}-${d} ${hh}:${mm}`;
    } catch (e) {
        return String(isoString);
    }
}
