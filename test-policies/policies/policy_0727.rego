package compliance.validation.user.validate.policy_0727

# Auto-generated policy 727 (Rego v1 syntax)
# Package: compliance.validation.user.validate

# Metadata
metadata := {
    "policy_id": "0727",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0727_allowed if {
    input.user.role == "admin"
}
default policy_0727_allowed = false
policy_0727_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
