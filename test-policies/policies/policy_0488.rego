package compliance.validation.policy.check.policy_0488

# Auto-generated policy 488 (Rego v1 syntax)
# Package: compliance.validation.policy.check

# Metadata
metadata := {
    "policy_id": "0488",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0488_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0488_allowed if {
    input.user.role == "admin"
}
policy_0488_allowed if {
    data.policies.compliance.enabled
}
default policy_0488_allowed = false
