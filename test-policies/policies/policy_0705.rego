package compliance.authentication.action.allow.policy_0705

# Auto-generated policy 705 (Rego v1 syntax)
# Package: compliance.authentication.action.allow

# Metadata
metadata := {
    "policy_id": "0705",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0705_allowed if {
    input.user.role == "admin"
}
policy_0705_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0705_allowed if {
    data.policies.compliance.enabled
}
