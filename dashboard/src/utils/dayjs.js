import dayjs from 'dayjs/esm';
import relativeTime from 'dayjs/esm/plugin/relativeTime';
import localizedFormat from 'dayjs/esm/plugin/localizedFormat';
import updateLocale from 'dayjs/esm/plugin/updateLocale';
import isToday from 'dayjs/esm/plugin/isToday';
import duration from 'dayjs/esm/plugin/duration';
import utc from 'dayjs/esm/plugin/utc';
import timezone from 'dayjs/esm/plugin/timezone';
import advancedFormat from 'dayjs/plugin/advancedFormat';

dayjs.extend(updateLocale);
dayjs.extend(relativeTime);
dayjs.extend(localizedFormat);
dayjs.extend(isToday);
dayjs.extend(duration);
dayjs.extend(utc);
dayjs.extend(timezone);
dayjs.extend(advancedFormat);

export function dayjsLocal(dateTimeString) {
	const localTimezone = dayjs.tz.guess();
	const systemTimezone = window.system_timezone || 'UTC';
	if (dateTimeString == null) return dayjs().tz(localTimezone);
	// Offset-aware inputs already identify an instant; only naive server values
	// need parsing in the timezone supplied by Press's dashboard boot data.
	if (
		typeof dateTimeString !== 'string' ||
		/(?:Z|[+-]\d{2}:?\d{2})$/i.test(dateTimeString)
	) {
		return dayjs(dateTimeString).tz(localTimezone);
	}
	return dayjs.tz(dateTimeString, systemTimezone).tz(localTimezone);
}

export function dayjsIST(dateTimeString) {
	return dayjs(dateTimeString).tz('Asia/Calcutta');
}

// Times of day (HH:mm) with no date of their own. Anchoring them to today keeps
// the offset right for timezones that observe DST.
export function timeLocal(serverTime) {
	return convertTimeOfDay(serverTime, 'Asia/Calcutta', dayjs.tz.guess());
}

export function timeServer(localTime) {
	return convertTimeOfDay(localTime, dayjs.tz.guess(), 'Asia/Calcutta');
}

function convertTimeOfDay(time, from, to) {
	const today = dayjs().format('YYYY-MM-DD');
	return dayjs.tz(`${today} ${time}`, from).tz(to).format('HH:mm');
}

export function dayjsFloorToMinutes(d, interval) {
	const minutes = d.minute();
	const floored = Math.floor(minutes / interval) * interval;

	return d.minute(floored).second(0).millisecond(0);
}

export default dayjs;
