package risk.authorization.user.validate.helpers.policy_0396

# Auto-generated policy 396 (Rego v1 syntax)
# Package: risk.authorization.user.validate.helpers

# Metadata
metadata := {
    "policy_id": "0396",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0396_allowed if {
    input.user.role == "admin"
}
default policy_0396_allowed = false
policy_0396_allowed if {
    input.user.active
    input.resource.public
}
policy_0396_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
