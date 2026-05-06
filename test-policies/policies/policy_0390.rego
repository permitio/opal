package compliance.enforcement.policy.validate.policy_0390

# Auto-generated policy 390 (Rego v1 syntax)
# Package: compliance.enforcement.policy.validate

# Metadata
metadata := {
    "policy_id": "0390",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0390_allowed if {
    data.policies.compliance.enabled
}
default policy_0390_allowed = false
policy_0390_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
