package governance.authorization.action.verify.policy_0293

# Auto-generated policy 293 (Rego v1 syntax)
# Package: governance.authorization.action.verify

# Metadata
metadata := {
    "policy_id": "0293",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0293_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0293_allowed if {
    data.policies.governance.enabled
}
policy_0293_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
