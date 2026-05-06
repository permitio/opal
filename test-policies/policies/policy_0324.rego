package audit.monitoring.resource.validate.policy_0324

# Auto-generated policy 324 (Rego v1 syntax)
# Package: audit.monitoring.resource.validate

# Metadata
metadata := {
    "policy_id": "0324",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0324_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0324_allowed if {
    input.user.role == "admin"
}
