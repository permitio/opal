package risk.monitoring.resource.check.policy_0660

# Auto-generated policy 660 (Rego v1 syntax)
# Package: risk.monitoring.resource.check

# Metadata
metadata := {
    "policy_id": "0660",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0660_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0660_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0660_allowed if {
    input.user.active
    input.resource.public
}
