# Certificate Verification Lifecycle
### Tamper-Proof & Externally Verifiable

This document outlines the lifecycle of a certificate in the UniversityX system, from upload to external verification.

## 1. Upload & Digital Fingerprinting
- **User Action**: Student uploads a certificate (PDF/Image).
- **System Action**: 
  - Immediately computes a **SHA-256 Hash** of the file content.
  - This hash acts as a unique "Digital Fingerprint". Any pixel-level modification to the file will drastically change this hash.

## 2. Auto-Verification Check
- **System Action**: Checks if this hash already exists in the `StudentActivity` verified database.
- **Scenario A (Match Found)**: 
  - If the hash matches a previously approved record (e.g., uploaded by another student or same student earlier):
  - **Status**: `auto_verified`
  - **Decision**: "Verified by previously stored hash."
  - **Token**: A public verification token is assigned immediately.
- **Scenario B (No Match)**:
  - **Status**: `pending`
  - **Action**: Sent to Faculty Queue.

## 3. Faculty Verification
- **User Action**: Faculty reviews the certificate and metadata.
- **Decision**: Approve or Reject.
- **On Approval**:
  - Status becomes `faculty_verified`.
  - The **SHA-256 Hash** is permanently linked to this valid record.
  - A unique **Verification Token** (e.g., `abc123_secure_token`) is generated.
  - This token enables external sharing without requiring login.

## 4. Re-Verification (Tamper-Proof)
- If the student (or anyone else) uploads the *exact same file* again:
  - The system re-computes the hash.
  - Finds the match from Step 3.
  - Automatically verifies it as `auto_verified` without troubling faculty.

## 5. External Verification (Employer/Placement)
- **User Action**: Student shares a link: `https://universityx.platform/verify/<token>`
- **Placement Officer**: Visits the link.
- **System Response**:
  - Looks up record by `token`.
  - Displays: Student Name, Activity Details, and the **Certificate Hash**.
  - No login required.
  - **Benefit**: Unlike simple PDFs which can be photoshopped, this link corresponds to a record on the institution's secure server, backed by the cryptographic hash of the original file.
