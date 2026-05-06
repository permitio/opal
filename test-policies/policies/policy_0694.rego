package compliance.validation.context.allow.policy_0694

# Auto-generated policy 694 (Rego v1 syntax)
# Package: compliance.validation.context.allow

# Metadata
metadata := {
    "policy_id": "0694",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0694_allowed = false
policy_0694_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0694_allowed if {
    input.user.role == "admin"
}
policy_0694_allowed if {
    data.policies.compliance.enabled
}
