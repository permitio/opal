package audit.monitoring.resource.deny.policy_0871

# Auto-generated policy 871 (Rego v1 syntax)
# Package: audit.monitoring.resource.deny

# Metadata
metadata := {
    "policy_id": "0871",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0871_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0871_allowed if {
    input.user.active
    input.resource.public
}
policy_0871_allowed if {
    input.user.role == "admin"
}
