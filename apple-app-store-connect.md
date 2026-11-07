# Complete App Store Connect fields in the browser

Use this field map with a tested app and an authorized release.
Copy [the example manifest](apple-app-store-connect.example.json) into private storage.
Replace its placeholders there. Never commit completed contact or account values.
The manifest records inputs. It does not execute browser actions.

## Before you change Apple state

1. Read the current release record and the owner's latest instructions.
2. Confirm the app, bundle, version, build, source commit, and tested archive.
3. Read Apple's existing builds before an upload. Never upload an identity twice.
4. Use the owner's browser profile. Confirm the authenticated app page.
5. Take a fresh browser snapshot. Reacquire field names and controls.
6. Change one section. Save it, reload it, and verify the stored result.

The field IDs below are observed browser identifiers, not Apple API contracts.
Apple can change its form. Never reuse stale snapshot references.
A successful click does not prove that Apple saves the value.
Keep proof files outside Git. Exclude session URLs, headers, tokens, and cookie values.

## App setup and app information

Open **Apps**, then the existing app. Create an app record only when none exists.

| Section | Values to prepare | Verification |
| --- | --- | --- |
| New app | Platform, name, primary language, registered bundle ID, SKU, user access | Reopen the app and match its identity. |
| App Information | Name, subtitle, primary category, optional secondary category | Reload the selected language and categories. |
| Content Rights | Whether you own or license all included content | Retain the actual license evidence. |
| Age Rating | Accurate answers for the shipped content and features | Read the generated ratings, including regional differences. |
| Regulations | App-specific permits and declarations when Apple requires them | Use owner facts. Do not infer legal status. |

Do not claim health services, medical-device status, or licensed rights without evidence.

## Version and localized metadata

Open **Distribution**, then the version marked **Prepare for Submission**.
Route shape: `/apps/{appId}/distribution/{platform}/version/inflight`.

| Field | Observed ID | Input rule |
| --- | --- | --- |
| Promotional Text | `promotionalText` | Describe the current shipped features. |
| Description | `description` | Explain useful tasks and material limits. |
| Keywords | `keywords` | Use relevant search terms. |
| Support URL | `supportUrl` | Verify the actual support content and contact route. |
| Marketing URL | `marketingUrl` | Use the appropriate public app or product page. |
| Version | `versionString` | Match the selected build's marketing version. |
| Copyright | `copyright` | Use the correct year and rights holder. |
| Routing coverage file | No stable ID recorded | Supply only when the app requires this file. |

Select **Save**. Reload the page and compare the stored values.
Check every required locale. Do not fill optional fields with invented content.

## Screenshots and other assets

| Item | Prepare | Verify |
| --- | --- | --- |
| iPhone screenshots | Actual app captures for Apple's accepted display sizes | Count and inspect the stored images after reload. |
| iPad screenshots | Actual iPad layouts when the binary supports iPad | Inspect readable text, navigation, and orientation. |
| App previews | Real footage when used | Check the selected locale and supported dimensions. |
| Header and search assets | Optional creative assets when supported by the current form | Do not confuse an empty optional slot with missing screenshots. |

Follow [Apple's asset guidance](https://developer.apple.com/app-store/product-page/).
Do not fabricate app screens with image generation.
Use generated artwork only where it truthfully represents the app.
Recapture evidence when a source change alters visible behavior.

## Select an existing build

1. Match the required build number and source evidence before changing the version.
2. Remove the old **version association** when replacement is necessary.
3. In the observed form, that control is the selected build row's **Delete** button.
4. Select **Add Build**, then the radio button for the exact existing build.
5. Select **Done**, then **Save** on the version page.
6. Reload. Verify the build number, version, and release setting.

The row control does not mean deleting the uploaded binary.
Do not select a similarly numbered build from another marketing version.
Never upload again to repair a selection error.

## App Review contact and release

| Field | Observed ID | Input rule |
| --- | --- | --- |
| First name | `contactFirstName` | Use the owner's real review contact. |
| Last name | `contactLastName` | Use the owner's real review contact. |
| Phone | `contactPhone` | Use a reachable owner-approved number with country code. |
| Email | `contactEmail` | Use a monitored owner-approved address. |
| Sign-in required | `appStoreReviewDetails_demoAccountRequired` | Enable only when review needs an account. |
| Demo credentials | Reacquire when shown | Provide a working review account, not an owner's password. |
| Notes | `notes` | Give repeatable steps and explain review-specific requirements. |
| Attachment | Reacquire when shown | Supply only relevant, inspected review material. |
| Manual release | `MANUAL` | Keep selected when the owner requests approval before release. |

Save and reload. Verify all four contact fields and the selected release radio button.
A private App Review phone is not automatically approved for public trader contact.

## App privacy

Open **App Privacy** at `/apps/{appId}/distribution/privacy`.

1. Select **Edit** beside **Privacy Policy**.
2. Fill `privacyPolicyUrl` with the complete, public app-specific policy.
3. Fill `privacyChoicesUrl` only when the app provides that optional page.
4. Select the dialog's **Save**. Reload and verify the link.
5. Check the data-type answers against the actual binary and included SDKs.
6. Select **Publish**, review the confirmation, then select **Publish** again.
7. Reload and verify the published label and policy URL.

A saved **Data Not Collected** draft is not a published label.
Use that answer only when the app's actual practices support it.
A policy title and HTTP200 do not prove that the full policy is public.
Read its complete text without an account, email unlock, or required cookie.
A static source file can receive analytics injection when deployed.
Check the deployed page. Separate website practices from native app practices accurately.

## Price and worldwide availability

Open **Pricing and Availability** at `/apps/{appId}/distribution/pricing`.

| Step | Action | Verify |
| --- | --- | --- |
| Price | Set the intended price and base country | Inspect prices in every selected territory. |
| Worldwide setup | Select **Set Up Availability**, then **All Countries or Regions** (`SETUP_ALL`) | Read Apple's current territory count. |
| Confirmation | Select **Next**, then **Confirm** | The observed form saves and opens `/pricing/availability`. |
| Reload | Reopen the availability detail | Confirm all intended territories and future-territory behavior. |

The availability confirmation can save automatically.
Do not assume that another **Save** button exists on its detail page.
Worldwide selection does not bypass territory-specific legal requirements.

To exclude the EU, deselect its current member states individually.
Use the [official EU member list](https://european-union.europa.eu/principles-countries-history/eu-countries_en); Europe includes countries outside the EU.
Select **Next**, then **Confirm**. Reload the availability detail.
Verify each excluded row shows **Not Available**. Verify that other intended territories remain selected.
Apple permits [availability changes later](https://developer.apple.com/help/app-store-connect/manage-your-apps-availability/manage-availability-for-your-app-on-the-app-store/).
Re-add EU storefronts when the owner chooses and the applicable requirements are met.
Do not declare non-trader status merely to avoid EU distribution. Preserve the owner's actual business facts.
Keep manual release selected on the version page.
Check Mac and Vision availability separately; do not claim untested compatibility.

## Trader status and owner verification

Apple distinguishes professional or business activity from a personal hobby.
An app's free price does not settle that question.
Ask the owner for the actual purpose of the app before choosing a status.
Do not infer status from an individual Developer Program membership.

For a trader, Apple can publish an address, phone number, and email in EU storefronts.
Get owner-approved **public** details. Do not reuse private review contacts by default.
Apple can require email and phone verification, payment details, and address documents.
Keep documents and verification codes outside Git and public proof.
The observed trader choice opens contact verification directly. Reacquire the next control instead of assuming another **Next** step.
Stop for the owner's unresolved facts or verification. Do not enter a guessed declaration.
Trader verification can continue separately after Apple accepts a review submission.
Do not claim that incomplete trader verification always blocks App Review.

Follow [Apple's trader requirements](https://developer.apple.com/help/app-store-connect/manage-compliance-information/manage-european-union-digital-services-act-trader-requirements).

## Encryption and internal testing

Check the signed binary's `Info.plist`, source, dependencies, and network behavior.
An absent `ITSAppUsesNonExemptEncryption` flag can leave a build missing export compliance.
Do not rebuild or reupload only to answer the existing build's questionnaire.
Use `usesNonExemptEncryption=false` only when that answer is correct and authorized.
Apple describes OS-only cryptography in its [export guidance](https://developer.apple.com/documentation/Security/complying-with-encryption-export-regulations).
Do not guess that a new dependency has the same encryption behavior.

An internal group with `hasAccessToAllBuilds=true` can receive an eligible build automatically.
After compliance changes, read the group again before adding a build.
A redundant add can return422 while the build becomes visible automatically.
Verify the actual group membership and internal testing state.
Do not create another group, tester invite, or upload to fix that race.

Check the existing beta localization before creating test notes.
An existing locale can have empty `whatsNew` text. Update that record instead of duplicating it.
A successful upload is not proof of processing, tester availability, or device installation.

## Submission and later releases

1. Recheck mandatory metadata, assets, live URLs, build identity, and owner declarations.
2. Confirm explicit submission authorization and the intended release setting.
3. Use **Add for Review** and inspect Apple's validation messages.
4. Resolve real blockers and recheck the prepared review item.
5. Record the resulting Apple status. **Ready for Review** is a draft, not a submission.
6. Select **Submit for Review** on the prepared review item. Verify **Waiting for Review** after submission.
7. Monitor Apple's result. Keep manual release until the owner authorizes release.

The local tools have separate limits:
[build evidence](apple-build-evidence.md), [internal-only upload](apple-testflight-upload.md),
and [push evidence](apple-push-evidence.md).
They do not form an automatic public upload or App Review pipeline.

## Multiple apps and publication limits

No general paid-account apps-per-day publication quota is verified in this runbook.
Do not convert that absence into a promise of unlimited approvals.
Apple's [Review Guidelines](https://developer.apple.com/app-store/review/guidelines/#spam) restrict duplicate apps and low-value template variants.
A name, color, location, or catalog change alone does not establish a distinct product.
Assess each site's native purpose, unique features, audience, and ongoing maintenance.
Consider one app with multiple catalogs when the workflows substantially overlap.
Do not use submission timing or extra accounts to evade review requirements.

The [external TestFlight review limit](https://developer.apple.com/help/app-store-connect/test-a-beta-version/invite-external-testers)
is separate from public app publication. Apple currently documents six builds within24hours for that review path.
Recheck current requirements before planning a fleet.
