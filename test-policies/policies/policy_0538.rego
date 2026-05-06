package audit.validation.user.allow.policy_0538

# Auto-generated policy 538 (Rego v1 syntax)
# Package: audit.validation.user.allow

# Metadata
metadata := {
    "policy_id": "0538",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0538_allowed if {
    input.user.role == "admin"
}
policy_0538_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0538_allowed = false
