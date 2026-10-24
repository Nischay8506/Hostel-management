# Cityhive UI/UX benchmark

Reviewed on 2026-10-21. This is a focused review of public product patterns, not a scoring or ranking exercise. Competitor pages are references only; Cityhive uses its own supplied emblem, wording, and components.

## Pages reviewed

- [Stanza Living](https://www.stanzaliving.com/) — property discovery and managed-living framing.
- [Zolo](https://zolostays.com/) — search-led discovery and sharing/location filters.
- [your-space](https://www.your-space.in/) — accommodation categories and enquiry path.
- [Colive property page](https://www.colive.com/hyderabad/pg-in-gachibowli-/colive-504-garnet/pg-in-pune) — property-level details and booking/enquiry actions.

These sites support familiar discovery patterns: start with a clear location/property choice, make room or sharing options scannable, and put an enquiry action beside relevant inventory. Cityhive adopts these patterns with its own navy/royal-blue/gold palette, supplied Cityhive emblem, and existing application APIs. Branch availability, room pricing, descriptions, and facilities are sourced from configured data; absent data is presented as unconfigured rather than filled in.

Cityhive deliberately retains the existing admission-review process: an enquiry does not reserve a room or guarantee admission. It also avoids copied competitor layouts and third-party logos or photographs. The current hero uses the existing project-generated representative room image, clearly labeled illustrative. Its provenance is recorded in the 2026-10-21 redesign section of VALIDATION.md. Approved branch photographs can be configured individually; no generated scene is presented as an actual Cityhive property.

## Technical references reviewed

- [Meta WhatsApp authentication category](https://whatsappbusiness.com/products/conversation-categories/authentication/)
- [Meta WhatsApp utility category](https://whatsappbusiness.com/products/conversation-categories/utility/)
- [Meta WhatsApp developer hub](https://whatsappbusiness.com/developers/developer-hub/)
- [OWASP Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html)

OWASP guidance informed short-lived, single-use OTP challenges, resend invalidation, attempt limits, and issuing the normal session only after OTP validation. The current Meta Graph API reference could not be retrieved during this implementation (the documentation request was rate-limited); the integration therefore uses configurable approved template names and must be validated against the account's current approved templates and API version before production delivery.
