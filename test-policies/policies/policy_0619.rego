package audit.authentication.context.check.policy_0619

# Auto-generated policy 619
# Package: audit.authentication.context.check

# Metadata
metadata := {
    "policy_id": "0619",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0619 = false
allowed_0619 {
    data.policies.audit.enabled
}

# Utility function for user info
