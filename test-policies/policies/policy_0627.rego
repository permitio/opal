package risk.authorization.resource.check.policy_0627

# Auto-generated policy 627 (Rego v1 syntax)
# Package: risk.authorization.resource.check

# Metadata
metadata := {
    "policy_id": "0627",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0627_allowed if {
    data.policies.risk.enabled
}
policy_0627_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0627_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
