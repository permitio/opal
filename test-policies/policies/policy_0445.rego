package risk.enforcement.action.deny.data.policy_0445

# Auto-generated policy 445 (Rego v1 syntax)
# Package: risk.enforcement.action.deny.data

# Metadata
metadata := {
    "policy_id": "0445",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0445_allowed if {
    data.policies.risk.enabled
}
policy_0445_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0445_allowed if {
    input.user.role == "admin"
}
policy_0445_allowed if {
    input.user.active
    input.resource.public
}
