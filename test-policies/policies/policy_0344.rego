package audit.validation.resource.check.utils.policy_0344

# Auto-generated policy 344 (Rego v1 syntax)
# Package: audit.validation.resource.check.utils

# Metadata
metadata := {
    "policy_id": "0344",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0344_allowed if {
    input.user.role == "admin"
}
policy_0344_allowed if {
    data.policies.audit.enabled
}
