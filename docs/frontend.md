# Frontend (`public/`)

Single-page web UI. No build step — plain HTML, CSS, and vanilla JavaScript served directly by Vercel's CDN.

## Files

| File | Purpose |
|---|---|
| `index.html` | Page structure and form markup |
| `app.js` | All interactive behaviour |
| `style.css` | Responsive layout, dark/light mode |

## User flow

1. User enters a URL in the form. An optional "Advanced" toggle exposes a max-pages field (default 30, range 1–100).
2. On submit, the JS validates the URL client-side, then `POST`s to `/api/generate`.
3. While the request is in flight, the submit button is disabled and a loading indicator is shown.
4. On success, the output section appears with the llms.txt content in a `<textarea>`, plus Copy and Download buttons.
5. On error (validation failure, network error, or API error response), an error banner is shown above the form.

## `app.js`

### State and DOM references

All DOM elements are looked up once at module load via `document.querySelector`. There is no framework or component abstraction — state is managed directly through DOM visibility and element attributes.

### Functions

#### `showError(message)`
Populates the error banner with `message` and makes it visible.

#### `hideError()`
Hides the error banner and clears its text.

#### `setLoading(isLoading)`
Toggles the loading indicator and disables/re-enables the submit button. Prevents double-submission during in-flight requests.

#### `validateClientUrl(value) -> string | null`
Returns an error message string if the URL is invalid, or `null` if it passes:
- Must not be empty.
- Must parse as a valid URL (via `new URL()`).
- Scheme must be `http` or `https`.

This is a client-side convenience check; the server validates independently.

### Event handlers

#### Form submit
1. Calls `validateClientUrl`; shows error and aborts if invalid.
2. Parses `maxPages` from the advanced field; clamps to `[1, 100]`, defaults to `30` if blank or out of range.
3. Calls `fetch('/api/generate', { method: 'POST', body: JSON.stringify({url, maxPages}) })`.
4. On non-OK HTTP status, reads the `error` field from the JSON response body and calls `showError`.
5. On success, sets the `<textarea>` value and scrolls the output section into view.
6. On network/parse failure, shows a generic error message.

#### Copy button
Uses `navigator.clipboard.writeText`. On success, briefly changes the button label to "Copied!" and restores it after 2 seconds. Shows an error if clipboard access is denied.

#### Download button
Creates a `Blob` from the textarea content, generates an object URL, triggers a click on a temporary `<a download="llms.txt">` element, then immediately revokes the object URL to free memory.

#### Advanced toggle
Toggles the visibility of the `#advanced-fields` container and updates `aria-expanded` on the toggle button for screen reader accessibility.

## No external dependencies

The frontend uses only native browser APIs:
- `fetch` for HTTP requests
- `navigator.clipboard` for copy-to-clipboard
- `URL` for client-side URL validation
- `Blob` / `URL.createObjectURL` for file download

No npm packages, no bundler, no framework.
