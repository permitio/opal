package audit.validation.resource.validate.core.policy_0424

# Auto-generated policy 424 (Rego v1 syntax)
# Package: audit.validation.resource.validate.core

# Metadata
metadata := {
    "policy_id": "0424",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0424_allowed if {
    input.user.active
    input.resource.public
}
default policy_0424_allowed = false
policy_0424_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
