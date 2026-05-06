package audit.validation.user.verify.policy_0542

# Auto-generated policy 542 (Rego v1 syntax)
# Package: audit.validation.user.verify

# Metadata
metadata := {
    "policy_id": "0542",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0542_allowed if {
    data.policies.audit.enabled
}
policy_0542_allowed if {
    input.user.role == "admin"
}
