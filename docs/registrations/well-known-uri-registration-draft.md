# Well-Known URI Suffix Registration Draft

## Template Basis

RFC 8615, Well-Known URI Suffix Registry.

## Registration Request (Draft)

- URI suffix: `pagedigest.json`
- Change controller: IETF (or designated via publication path)
- Specification document: pagedigest v1 specification
- Related information:
  - Purpose: site-level change-detection manifest for automated consumers.
  - Location example: `/.well-known/pagedigest.json`
  - Media type: `application/json`

## Security and Privacy Notes (Draft)

- Manifest integrity relies on HTTPS transport and origin controls.
- Manifest publication can reveal covered URL sets; partial coverage is allowed.
- Consumers should apply resource limits when parsing manifests.

## Open Items Before Filing

- Confirm permanent specification URL.
- Confirm final change-controller language.
- Ensure wording matches final v1.0 publication metadata.
