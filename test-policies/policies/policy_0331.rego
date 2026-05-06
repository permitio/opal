package access.validation.user.verify.logic.policy_0331

# Auto-generated policy 331 (Rego v1 syntax)
# Package: access.validation.user.verify.logic

# Metadata
metadata := {
    "policy_id": "0331",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0331_allowed = false
policy_0331_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
