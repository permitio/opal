package risk.authorization.resource.check.policy_0245

# Auto-generated policy 245 (Rego v1 syntax)
# Package: risk.authorization.resource.check

# Metadata
metadata := {
    "policy_id": "0245",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0245_allowed if {
    input.user.role == "admin"
}
policy_0245_allowed if {
    input.user.active
    input.resource.public
}
policy_0245_allowed if {
    data.policies.risk.enabled
}
