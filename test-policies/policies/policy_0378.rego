package risk.authorization.user.validate.policy_0378

# Auto-generated policy 378 (Rego v1 syntax)
# Package: risk.authorization.user.validate

# Metadata
metadata := {
    "policy_id": "0378",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0378_allowed if {
    input.user.active
    input.resource.public
}
policy_0378_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
