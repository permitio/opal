package risk.validation.resource.validate.helpers.policy_0570

# Auto-generated policy 570 (Rego v1 syntax)
# Package: risk.validation.resource.validate.helpers

# Metadata
metadata := {
    "policy_id": "0570",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0570_allowed if {
    data.policies.risk.enabled
}
policy_0570_allowed if {
    input.user.active
    input.resource.public
}
