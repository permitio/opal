package compliance.validation.action.allow.policy_0823

# Auto-generated policy 823 (Rego v1 syntax)
# Package: compliance.validation.action.allow

# Metadata
metadata := {
    "policy_id": "0823",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0823_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0823_allowed if {
    input.user.role == "admin"
}
