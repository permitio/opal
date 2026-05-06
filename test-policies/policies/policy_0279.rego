package risk.authorization.resource.validate.policy_0279

# Auto-generated policy 279 (Rego v1 syntax)
# Package: risk.authorization.resource.validate

# Metadata
metadata := {
    "policy_id": "0279",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0279_allowed if {
    data.policies.risk.enabled
}
default policy_0279_allowed = false
policy_0279_allowed if {
    input.user.role == "admin"
}
