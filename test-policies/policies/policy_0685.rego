package risk.validation.action.verify.helpers.policy_0685

# Auto-generated policy 685 (Rego v1 syntax)
# Package: risk.validation.action.verify.helpers

# Metadata
metadata := {
    "policy_id": "0685",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0685_allowed if {
    input.user.active
    input.resource.public
}
policy_0685_allowed if {
    data.policies.risk.enabled
}
default policy_0685_allowed = false
policy_0685_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
