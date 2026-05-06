package governance.monitoring.user.deny.policy_0156

# Auto-generated policy 156 (Rego v1 syntax)
# Package: governance.monitoring.user.deny

# Metadata
metadata := {
    "policy_id": "0156",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0156_allowed if {
    input.user.active
    input.resource.public
}
policy_0156_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
