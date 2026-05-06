package audit.validation.resource.verify.logic.policy_0495

# Auto-generated policy 495
# Package: audit.validation.resource.verify.logic

# Metadata
metadata := {
    "policy_id": "0495",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0495 = false
allowed_0495 {
    data.policies.audit.enabled
}

# Utility function for user info
