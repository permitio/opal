package compliance.enforcement.user.check.policy_0080

# Auto-generated policy 80 (Rego v1 syntax)
# Package: compliance.enforcement.user.check

# Metadata
metadata := {
    "policy_id": "0080",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0080_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0080_allowed if {
    data.policies.compliance.enabled
}
policy_0080_allowed if {
    input.user.active
    input.resource.public
}
