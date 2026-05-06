package audit.authentication.user.validate.policy_0574

# Auto-generated policy 574 (Rego v1 syntax)
# Package: audit.authentication.user.validate

# Metadata
metadata := {
    "policy_id": "0574",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0574_allowed if {
    input.user.role == "admin"
}
policy_0574_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
