package risk.validation.user.validate.policy_0333

# Auto-generated policy 333 (Rego v1 syntax)
# Package: risk.validation.user.validate

# Metadata
metadata := {
    "policy_id": "0333",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0333_allowed if {
    input.user.active
    input.resource.public
}
policy_0333_allowed if {
    data.policies.risk.enabled
}
policy_0333_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
